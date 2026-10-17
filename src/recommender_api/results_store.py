"""Zapisane rekomendacje (tabela recommendations): gotowe zestawy kart per użytkownik.

Klucz: userId + setKey = rodzaj okna, daty, limit i wpisana fraza, np.
"today#2026-10-17#2026-10-17#12#" albo "date#2026-10-30#2026-10-30#12#jazz".

Rekord: body (zestaw kart jako JSON), prefsHash (odcisk preferencji, dla których policzony),
generatedAt, expiresAt (TTL: dzień po końcu okna). Podczas liczenia na tym samym rekordzie
leży claim (claimHash + claimedAt): inni nie liczą drugi raz, a stary zestaw dalej się wyświetla.
Po CLAIM_SECONDS claim wygasa (liczenie padło) i można go przejąć.

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
CLAIM_SECONDS = 180  # liczenie dwóch faz (wektory + AI) trwa zwykle do minuty


def set_key(when: str, span: tuple[date, date], query: str, limit: int) -> str:
    return f"{when}#{span[0].isoformat()}#{span[1].isoformat()}#{limit}#{query.lower()}"


def prefs_hash(prefs: dict, rag_profile: str | None) -> str:
    payload = json.dumps([RESULTS_VERSION, prefs, rag_profile], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def expires_at(span: tuple[date, date]) -> int:
    return int(datetime.combine(span[1] + timedelta(days=1), time(), tzinfo=WARSAW).timestamp())


def claimed(item: dict | None, now: datetime) -> bool:
    """Czy ktoś właśnie liczy ten zestaw."""
    return bool(item and item.get("claimedAt") and int(item["claimedAt"]) >= int(now.timestamp()) - CLAIM_SECONDS)


class ResultsStore:
    def __init__(self, table=None):
        self.table = table
        self._memory: dict[tuple[str, str], dict] = {}

    def get(self, user_id: str, key: str) -> dict | None:
        if self.table is None:
            return self._memory.get((user_id, key))
        # Spójny odczyt: claim i nowy zestaw mają być widoczne od razu
        return self.table.get_item(Key={"userId": user_id, "setKey": key}, ConsistentRead=True).get("Item")

    def claim(self, user_id: str, key: str, fingerprint: str, now: datetime) -> bool:
        """Zaznacza, że zestaw liczy się dla tych preferencji. False, gdy ktoś już go liczy."""
        stamp = int(now.timestamp())
        if self.table is None:
            current = self._memory.get((user_id, key)) or {}
            if claimed(current, now) and current.get("claimHash") == fingerprint:
                return False
            self._memory[(user_id, key)] = {"userId": user_id, "setKey": key, "expiresAt": stamp + 86400,
                                            **current, "claimHash": fingerprint, "claimedAt": stamp}
            return True
        try:
            self.table.update_item(
                Key={"userId": user_id, "setKey": key},
                UpdateExpression="SET claimHash = :h, claimedAt = :now, expiresAt = if_not_exists(expiresAt, :exp)",
                ConditionExpression="attribute_not_exists(claimedAt) OR claimedAt < :cutoff OR claimHash <> :h",
                ExpressionAttributeValues={":h": fingerprint, ":now": stamp, ":exp": stamp + 86400,
                                           ":cutoff": stamp - CLAIM_SECONDS},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def put(self, user_id: str, key: str, fingerprint: str, body: dict, expires: int) -> None:
        """Zapisuje zestaw (cały rekord, bez claimu) - chyba że w międzyczasie zestaw przejął ktoś,
        kto liczy go dla nowszych preferencji."""
        item = {
            "userId": user_id,
            "setKey": key,
            "prefsHash": fingerprint,
            "generatedAt": body["generatedAt"],
            # JSON jako tekst: bez konwersji liczb na Decimal i z powrotem
            "body": json.dumps(body, ensure_ascii=False, default=str),
            "expiresAt": expires,
        }
        if self.table is None:
            current = self._memory.get((user_id, key)) or {}
            if current.get("claimHash") in (None, fingerprint):
                self._memory[(user_id, key)] = item
            return
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(claimHash) OR claimHash = :h",
                                ExpressionAttributeValues={":h": fingerprint})
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def release(self, user_id: str, key: str, fingerprint: str) -> None:
        """Zdejmuje claim po nieudanym liczeniu, żeby następne zapytanie od razu spróbowało ponownie."""
        if self.table is None:
            current = self._memory.get((user_id, key))
            if current and current.get("claimHash") == fingerprint:
                current.pop("claimHash", None)
                current.pop("claimedAt", None)
            return
        try:
            self.table.update_item(
                Key={"userId": user_id, "setKey": key},
                UpdateExpression="REMOVE claimHash, claimedAt",
                ConditionExpression="claimHash = :h",
                ExpressionAttributeValues={":h": fingerprint},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

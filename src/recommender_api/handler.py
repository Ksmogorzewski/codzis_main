"""Rekomendacje (RAG) dla portalu klienta: Lambda z obrazu kontenera (pakiet recommender/).

    GET /api/recommendations?when=today|tomorrow|weekend|week|date&date=RRRR-MM-DD&q=...&limit=12
        HTTP API + JWT authorizer Cognito; profil z tabeli users (preferences, ragProfile).
        Zestawy są zapisywane (tabela recommendations, results_store.py) i liczone ponownie dopiero
        po zmianie profilu, po RESULTS_MAX_AGE_HOURS albo gdy zostało w nich za mało niezakończonych
        wydarzeń. 202 {"status": "preparing"} = zestaw właśnie się liczy - zapytaj za chwilę.
    {"action": "precompute", "userId": "..."}  dziś, jutro i weekend dla jednej osoby
        (client-api po zapisaniu profilu i przy logowaniu)
    {"action": "precompute"}  to samo dla wszystkich aktywnych (EventBridge w nocy)
    {"action": "refresh"}  przebudowa indeksu w S3 (EventBridge co 30 min, scripts/recommender-refresh.sh)
    {"action": "warmup"}   model + indeks w pamięci, żeby liczenie nie czekało na zimny start

Model i indeks ładują się dopiero, gdy trzeba coś policzyć (nie przy imporcie ani przy podawaniu
zapisanego zestawu): faza INIT Lambdy ma limit 10 s, a sam import torcha potrafi tyle trwać.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.conditions import Attr

from index_store import FileStore, S3Store, load_events_file, refresh, scan_events
from present import card, still_on
from recommender import DEFAULT_MODEL, EmbeddingModel, Recommender
from results_store import ResultsStore, expires_at, prefs_hash, set_key
from user_context import AREAS, WINDOWS, build_context, start_area, window

log = logging.getLogger()
log.setLevel(logging.INFO)

WARSAW = ZoneInfo("Europe/Warsaw")
MODEL_PATH = os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL  # w obrazie: katalog z zapisanym modelem
LLM_ENABLED = os.environ.get("LLM_ENABLED", "true") == "true"
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "12"))  # potem ranking bez LLM; HTTP API czeka max 30 s
LLM_POOL = 16                # tylu najlepszych kandydatów układa LLM
INDEX_CHECK_SECONDS = 300    # co tyle sprawdzamy, czy w S3 jest nowszy indeks
RESULTS_MAX_AGE = timedelta(hours=float(os.environ.get("RESULTS_MAX_AGE_HOURS", "12")))  # łapie nowe eventy
PRECOMPUTE_ACTIVE_DAYS = int(os.environ.get("PRECOMPUTE_ACTIVE_DAYS", "14"))
DEFAULT_SETS = ["today", "tomorrow", "weekend"]  # liczone z góry: w nocy, po zmianie profilu, przy logowaniu
MIN_RESULTS = 4              # mniej propozycji -> poszerzamy obszar (okolica -> sąsiednie -> cała Warszawa)
DEFAULT_LIMIT, MAX_LIMIT = 12, 24
MAX_QUERY = 120

if os.environ.get("INDEX_PATH"):
    store = FileStore(os.environ["INDEX_PATH"])
else:
    store = S3Store(boto3.client("s3"), os.environ["INDEX_BUCKET"], os.environ.get("INDEX_KEY", "recommender/index.npz"))
dynamodb = boto3.resource("dynamodb")
users = dynamodb.Table(os.environ["USERS_TABLE"]) if os.environ.get("USERS_TABLE") else None
results = ResultsStore(dynamodb.Table(os.environ["RESULTS_TABLE"]) if os.environ.get("RESULTS_TABLE") else None)

_model = None
_engine = None
_engine_version = None
_engine_meta: dict = {}
_checked_at = 0.0
_api_key: str | None | bool = False  # False = jeszcze nie pobrany


class ApiError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.body = {"error": message, **extra}


def handler(event, context):
    if "routeKey" in event:
        return _http(event)
    match event.get("action"):
        case "refresh":
            return refresh_index()
        case "precompute":
            return precompute(event.get("userId"), context)
        case "warmup":
            try:
                _current_engine()
            except ApiError as e:
                return {"warm": False, "reason": e.body["error"]}
            return {"warm": True, "index": _engine_meta.get("builtAt")}
    raise ValueError(f"Nieznana akcja: {event.get('action')!r}")


def _http(event):
    try:
        if event["routeKey"] != "GET /api/recommendations":
            raise ApiError(404, "Nie znaleziono")
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
        body = get_recommendations(claims["sub"], event.get("queryStringParameters") or {})
        if body is None:  # liczy się teraz gdzie indziej (np. po zmianie profilu)
            return _response(202, {"status": "preparing", "retryAfter": 2})
        return _response(200, body)
    except ApiError as e:
        return _response(e.status, e.body)


def get_recommendations(user_id: str, params: dict) -> dict | None:
    when = params.get("when") or "today"
    if when not in WINDOWS:
        raise ApiError(400, "Nieznany zakres czasu", fields=["when"])
    query = " ".join((params.get("q") or "").split())[:MAX_QUERY]
    try:
        limit = min(max(int(params.get("limit") or DEFAULT_LIMIT), 1), MAX_LIMIT)
    except ValueError:
        raise ApiError(400, "Niepoprawny limit", fields=["limit"])

    # Spójny odczyt: strona pyta o rekomendacje zaraz po zapisaniu nowego profilu
    user = users.get_item(Key={"userId": user_id}, ConsistentRead=True).get("Item") or {}
    if not user.get("preferences"):
        raise ApiError(409, "Uzupełnij profil, żeby zobaczyć rekomendacje.", code="needs_onboarding")

    now = datetime.now(WARSAW)
    try:
        span = window(when, now.date(), params.get("date"))
    except ValueError as e:
        raise ApiError(400, str(e), fields=["date"])
    return recommendation_set(user_id, user["preferences"], user.get("ragProfile"), when, span, query, limit, now)


def recommendation_set(user_id, prefs, rag_profile, when, span, query, limit, now) -> dict | None:
    """Zapisany zestaw albo policzony teraz (i zapisany); None = ktoś inny właśnie go liczy."""
    key = set_key(when, span, query, limit)
    fingerprint = prefs_hash(prefs, rag_profile)
    item = results.get(user_id, key)
    if item and (body := _reusable(item, fingerprint, now)):
        return body
    if not results.claim(user_id, key, fingerprint, now):
        return None
    try:
        body = compute(prefs, rag_profile, when, span, query, limit, now)
    except Exception:
        results.release(user_id, key, fingerprint)
        raise
    results.put(user_id, key, fingerprint, body, expires_at(span))
    return {**body, "cached": False}


def _reusable(item: dict, fingerprint: str, now: datetime) -> dict | None:
    if item.get("status") != "ready" or item.get("prefsHash") != fingerprint:
        return None
    if now - datetime.fromisoformat(item["generatedAt"]) > RESULTS_MAX_AGE:
        return None
    body = json.loads(item["body"])
    # Zestaw na dziś ogląda się do wieczora: bez wydarzeń, które już się skończyły
    items = [c for c in body["items"] if still_on(c, now)]
    if len(items) < min(MIN_RESULTS, len(body["items"])):
        return None
    return {**body, "items": items, "cached": True}


def compute(prefs, rag_profile, when, span, query, limit, now) -> dict:
    engine = _current_engine()
    first_area = start_area(prefs)
    for area in AREAS[AREAS.index(first_area):]:
        context = build_context(prefs, rag_profile, span, query, now, area)
        if len(engine.retriever.retrieve(context, top_k=MIN_RESULTS)) >= MIN_RESULTS:
            break

    started = time.monotonic()
    found = engine.recommend(context, top_k=limit, pool=max(limit, LLM_POOL), explain=LLM_ENABLED)
    log.info("Rekomendacje: when=%s area=%s query=%s -> %d (%s) w %.1f s%s", when, area, bool(query), len(found),
             engine.last_ranking, time.monotonic() - started, f"; LLM: {engine.last_error}" if engine.last_error else "")
    return {
        "generatedAt": now.isoformat(timespec="seconds"),
        "when": when,
        "window": {"from": context["date_from"], "to": context["date_to"]},
        "query": query or None,
        "district": prefs.get("district"),
        "area": area,
        "areaRelaxed": area != first_area,
        "ranking": engine.last_ranking,
        "items": [card(c, query) for c in found],
        "index": {"builtAt": _engine_meta.get("builtAt"), "events": _engine_meta.get("events")},
    }


def precompute(user_id: str | None = None, context=None) -> dict:
    """Zestawy na dziś, jutro i weekend: dla jednej osoby (po zmianie profilu, przy logowaniu) albo dla
    wszystkich aktywnych w ostatnich PRECOMPUTE_ACTIVE_DAYS dniach (w nocy). Ważne zestawy zostają."""
    if user_id:
        item = users.get_item(Key={"userId": user_id}, ConsistentRead=True).get("Item")
        todo = [item] if item and item.get("preferences") else []
    else:
        todo = _active_users()

    stats = {"users": 0, "computed": 0, "reused": 0, "busy": 0, "failed": 0, "stopped": False}
    for user in todo:
        if context and context.get_remaining_time_in_millis() < 90_000:
            stats["stopped"] = True  # reszta policzy się przy wejściu na stronę
            break
        stats["users"] += 1
        now = datetime.now(WARSAW)
        for when in DEFAULT_SETS:
            try:
                body = recommendation_set(user["userId"], user["preferences"], user.get("ragProfile"), when,
                                          window(when, now.date()), "", DEFAULT_LIMIT, now)
            except Exception:
                log.exception("Nie udało się przeliczyć zestawu %s", when)
                stats["failed"] += 1
                continue
            stats["busy" if body is None else "reused" if body["cached"] else "computed"] += 1
    log.info("Przeliczenie zestawów: %s", stats)
    return stats


def _active_users() -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=PRECOMPUTE_ACTIVE_DAYS)).isoformat()
    kwargs = {
        "FilterExpression": Attr("preferences").exists() & Attr("lastLoginAt").gte(since),
        "ProjectionExpression": "userId, preferences, ragProfile",
    }
    found = []
    while True:
        page = users.scan(**kwargs)
        found += page["Items"]
        if "LastEvaluatedKey" not in page:
            return found
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def refresh_index() -> dict:
    started = time.monotonic()
    if os.environ.get("EVENTS_FILE"):
        raw = load_events_file(os.environ["EVENTS_FILE"])
    else:
        raw = scan_events(dynamodb.Table(os.environ["EVENTS_TABLE"]))
    index, stats = refresh(raw, store.load(), _load_model)
    if index:
        store.save(index)
    stats.update(changed=index is not None, seconds=round(time.monotonic() - started, 1))
    log.info("Odświeżenie indeksu: %s", stats)
    return stats


def _current_engine() -> Recommender:
    """Recommender na aktualnym indeksie (sprawdzanym co INDEX_CHECK_SECONDS)."""
    global _engine, _engine_version, _engine_meta, _checked_at
    if _engine is not None and time.monotonic() - _checked_at < INDEX_CHECK_SECONDS:
        return _engine
    _checked_at = time.monotonic()
    version = store.version()
    if version is not None and version != _engine_version:
        index = store.load()
        if index is not None:
            _engine = Recommender(index.events, model=_load_model(), api_key=_deepseek_key(),
                                  index=index.vector_index(), llm_timeout=LLM_TIMEOUT)
            _engine_version, _engine_meta = version, index.meta
            log.info("Wczytano indeks z %s: %d eventów", index.meta.get("builtAt"), len(index.events))
    if _engine is None:
        raise ApiError(503, "Rekomendacje są jeszcze przygotowywane – spróbuj za kilka minut.")
    return _engine


def _load_model() -> EmbeddingModel:
    global _model
    if _model is None:
        started = time.monotonic()
        _model = EmbeddingModel(MODEL_PATH)  # tu dopiero import torcha
        log.info("Model embeddingów wczytany w %.1f s", time.monotonic() - started)
    return _model


def _deepseek_key() -> str | None:
    """Klucz z SSM (ten sam co taggera); bez klucza ranking jest czysto wektorowy."""
    global _api_key
    if _api_key is False:
        _api_key = os.environ.get("DEEPSEEK_API_KEY") or None
        name = os.environ.get("DEEPSEEK_API_KEY_PARAM")
        if LLM_ENABLED and name and not _api_key:
            try:
                value = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"].strip()
                _api_key = value if value and value != "CHANGE_ME" else None
            except Exception:
                log.exception("Nie udało się pobrać klucza DeepSeek - ranking bez LLM")
    return _api_key


def _response(status: int, body) -> dict:
    # Nagłówki CORS dodaje HTTP API (cors_configuration w infra/client_api.tf)
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }

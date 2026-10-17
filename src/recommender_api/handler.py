"""Rekomendacje (RAG) dla portalu klienta: Lambda z obrazu kontenera (pakiet recommender/).

    GET /api/recommendations?when=today|tomorrow|weekend|week&q=...&limit=12
        HTTP API + JWT authorizer Cognito; profil z tabeli users (preferences, ragProfile)
    {"action": "refresh"}  przebudowa indeksu w S3 (EventBridge co 30 min, scripts/recommender-refresh.sh)
    {"action": "warmup"}   model + indeks w pamięci, żeby użytkownik nie czekał na zimny start

Model i indeks ładują się przy pierwszym wywołaniu, nie przy imporcie: faza INIT Lambdy ma
limit 10 s, a sam import torcha potrafi tyle trwać.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3

from index_store import FileStore, S3Store, load_events_file, refresh, scan_events
from present import card
from recommender import DEFAULT_MODEL, EmbeddingModel, Recommender
from user_context import AREAS, WINDOWS, build_context, start_area

log = logging.getLogger()
log.setLevel(logging.INFO)

WARSAW = ZoneInfo("Europe/Warsaw")
MODEL_PATH = os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL  # w obrazie: katalog z zapisanym modelem
LLM_ENABLED = os.environ.get("LLM_ENABLED", "true") == "true"
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "12"))  # potem ranking bez LLM; HTTP API czeka max 30 s
LLM_POOL = 16                # tylu najlepszych kandydatów układa LLM
INDEX_CHECK_SECONDS = 300    # co tyle sprawdzamy, czy w S3 jest nowszy indeks
CACHE_SECONDS = 600          # te same parametry -> ta sama odpowiedź, bez ponownego wołania LLM
MIN_RESULTS = 4              # mniej propozycji -> poszerzamy obszar (okolica -> sąsiednie -> cała Warszawa)
DEFAULT_LIMIT, MAX_LIMIT = 12, 24
MAX_QUERY = 120

if os.environ.get("INDEX_PATH"):
    store = FileStore(os.environ["INDEX_PATH"])
else:
    store = S3Store(boto3.client("s3"), os.environ["INDEX_BUCKET"], os.environ.get("INDEX_KEY", "recommender/index.npz"))
dynamodb = boto3.resource("dynamodb")
users = dynamodb.Table(os.environ["USERS_TABLE"]) if os.environ.get("USERS_TABLE") else None

_model = None
_engine = None
_engine_version = None
_engine_meta: dict = {}
_checked_at = 0.0
_api_key: str | None | bool = False  # False = jeszcze nie pobrany
_cache: dict[str, tuple[float, dict]] = {}


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
        return _response(200, get_recommendations(claims["sub"], event.get("queryStringParameters") or {}))
    except ApiError as e:
        return _response(e.status, e.body)


def get_recommendations(user_id: str, params: dict) -> dict:
    when = params.get("when") or "today"
    if when not in WINDOWS:
        raise ApiError(400, "Nieznany zakres czasu", fields=["when"])
    query = " ".join((params.get("q") or "").split())[:MAX_QUERY]
    try:
        limit = min(max(int(params.get("limit") or DEFAULT_LIMIT), 1), MAX_LIMIT)
    except ValueError:
        raise ApiError(400, "Niepoprawny limit", fields=["limit"])

    user = users.get_item(Key={"userId": user_id}).get("Item") or {}
    prefs = user.get("preferences")
    if not prefs:
        raise ApiError(409, "Uzupełnij profil, żeby zobaczyć rekomendacje.", code="needs_onboarding")

    engine = _current_engine()
    key = hashlib.sha1(
        json.dumps([user_id, _engine_version, prefs, user.get("ragProfile"), when, query.lower(), limit],
                   sort_keys=True, default=str).encode()
    ).hexdigest()
    if (hit := _cache.get(key)) and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]

    now = datetime.now(WARSAW)
    first_area = start_area(prefs)
    for area in AREAS[AREAS.index(first_area):]:
        context = build_context(prefs, user.get("ragProfile"), when, query, now, area)
        if len(engine.retriever.retrieve(context, top_k=MIN_RESULTS)) >= MIN_RESULTS:
            break

    started = time.monotonic()
    results = engine.recommend(context, top_k=limit, pool=max(limit, LLM_POOL), explain=LLM_ENABLED)
    log.info("Rekomendacje: when=%s area=%s query=%s -> %d (%s) w %.1f s%s", when, area, bool(query), len(results),
             engine.last_ranking, time.monotonic() - started, f"; LLM: {engine.last_error}" if engine.last_error else "")

    body = {
        "generatedAt": now.isoformat(timespec="seconds"),
        "when": when,
        "window": {"from": context["date_from"], "to": context["date_to"]},
        "query": query or None,
        "district": prefs.get("district"),
        "area": area,
        "areaRelaxed": area != first_area,
        "ranking": engine.last_ranking,
        "items": [card(c, query) for c in results],
        "index": {"builtAt": _engine_meta.get("builtAt"), "events": _engine_meta.get("events")},
    }
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.monotonic(), body)
    return body


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
            _cache.clear()
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

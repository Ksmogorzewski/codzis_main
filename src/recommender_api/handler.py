"""Rekomendacje (RAG) dla portalu klienta: Lambda z obrazu kontenera (pakiet recommender/).

    GET /api/recommendations?when=today|tomorrow|weekend|week|date&date=RRRR-MM-DD&q=...&limit=16
        HTTP API + JWT authorizer Cognito; profil z tabeli users (preferences, ragProfile).
        Bez q zestaw układa profil; z q fraza dominuje (szukamy w całej Warszawie, bez twardych
        filtrów z onboardingu), a preferencje z profilu rozstrzygają tylko remisy.
        Zawsze odpowiada od razu z zapisanego zestawu (tabela recommendations, results_store.py),
        także nieaktualnego - wtedy z "updating": true i nowym liczonym w tle. Gdy model i indeks
        są już w pamięci (ciepła instancja), faza 1 liczy się od razu w tej samej Lambdzie i pierwsze
        żądanie zwraca karty zamiast czekać; 202 {"status": "preparing"} = zestawu jeszcze nie ma
        (albo zmienił się profil, albo instancja jest zimna) i właśnie liczy się w tle.
    {"action": "compute", ...}  jeden zestaw w tle (zlecany przez GET; bez limitu 30 s HTTP API)
    {"action": "precompute", "userId": "..."}  dziś, jutro i weekend dla jednej osoby
        (client-api po zapisaniu profilu i przy logowaniu)
    {"action": "precompute"}  to samo dla wszystkich aktywnych (EventBridge w nocy)
    {"action": "refresh"}  przebudowa indeksu w S3 (EventBridge co 30 min, scripts/recommender-refresh.sh)
    {"action": "warmup"}   model + indeks w pamięci, żeby liczenie nie czekało na zimny start

Liczenie ma dwie fazy: najpierw filtry + wektory (sekundy; zestaw od razu trafia do zapisu,
z "refining": true), potem DeepSeek układa kolejność i pisze uzasadnienia (do LLM_TIMEOUT s).

Model i indeks ładują się dopiero, gdy trzeba coś policzyć (nie przy imporcie ani przy podawaniu
zapisanego zestawu): faza INIT Lambdy ma limit 10 s, a sam import torcha potrafi tyle trwać.
"""

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.conditions import Attr

from index_store import FileStore, S3Store, load_events_file, refresh, scan_events
from present import card, still_on
from recommender import DEFAULT_MODEL, EmbeddingModel, Recommender
from results_store import RESULTS_VERSION, ResultsStore, claimed, expires_at, prefs_hash, set_key
from user_context import AREAS, WINDOWS, build_context, start_area, window

log = logging.getLogger()
log.setLevel(logging.INFO)

WARSAW = ZoneInfo("Europe/Warsaw")
MODEL_PATH = os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL  # w obrazie: katalog z zapisanym modelem
LLM_ENABLED = os.environ.get("LLM_ENABLED", "true") == "true"
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))  # LLM woła tylko liczenie w tle
INDEX_CHECK_SECONDS = 300    # co tyle sprawdzamy, czy w S3 jest nowszy indeks
RESULTS_MAX_AGE = timedelta(hours=float(os.environ.get("RESULTS_MAX_AGE_HOURS", "12")))  # łapie nowe eventy
REFINE_SECONDS = 300         # dłużej faza AI nie trwa; potem zestaw zostaje z kolejnością wektorową
PRECOMPUTE_ACTIVE_DAYS = int(os.environ.get("PRECOMPUTE_ACTIVE_DAYS", "14"))
DEFAULT_SETS = ["today", "tomorrow", "weekend"]  # liczone z góry: w nocy, po zmianie profilu, przy logowaniu
MIN_RESULTS = 4              # mniej propozycji -> poszerzamy obszar (okolica -> sąsiednie -> cała Warszawa)
# = RECOMMENDATIONS_LIMIT we froncie (hooks/use-recommendations.query.ts): z tym limitem liczą się zestawy
# z góry, więc inny limit w zapytaniu to inny klucz zestawu i liczenie od zera
DEFAULT_LIMIT, MAX_LIMIT = 16, 24
MAX_QUERY = 120

if os.environ.get("INDEX_PATH"):
    store = FileStore(os.environ["INDEX_PATH"])
else:
    store = S3Store(boto3.client("s3"), os.environ["INDEX_BUCKET"], os.environ.get("INDEX_KEY", "recommender/index.npz"))
dynamodb = boto3.resource("dynamodb")
users = dynamodb.Table(os.environ["USERS_TABLE"]) if os.environ.get("USERS_TABLE") else None
results = ResultsStore(dynamodb.Table(os.environ["RESULTS_TABLE"]) if os.environ.get("RESULTS_TABLE") else None)
lambda_client = boto3.client("lambda")

_model = None
_engine = None
_engine_version = None
_engine_meta: dict = {}
_checked_at = 0.0
_rejected_version = None  # indeks zbudowany innym modelem niż ten w obrazie (czeka na przebudowę)
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
        case "compute":
            return compute_set(event)
        case "precompute":
            return precompute(event.get("userId"), context)
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
        body = get_recommendations(claims["sub"], event.get("queryStringParameters") or {})
        if body is None:
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

    key = set_key(when, span, query, limit)
    fingerprint = prefs_hash(user["preferences"], user.get("ragProfile"))
    body, fresh = _stored(results.get(user_id, key), fingerprint, now)
    if not fresh:
        job = {"when": when, "from": span[0].isoformat(), "to": span[1].isoformat(),
               "q": query, "limit": limit}
        try:
            if results.claim(user_id, key, fingerprint, now):
                if _engine is not None:
                    # Ciepła instancja: faza 1 (filtry + wektory) od razu w tej samej Lambdzie -
                    # karty w ~100 ms zamiast 202 + 2 s. AI (faza 2) i tak liczy się w tle, jak dotąd.
                    _compute_inline(user_id, user, key, fingerprint, job, now)
                    body, _ = _stored(results.get(user_id, key), fingerprint, now)
                    _start_compute(user_id, key, fingerprint, job)
                else:
                    # Zimna instancja: liczenie w tle (jak dotąd), stary zestaw pokazujemy dalej.
                    _start_compute(user_id, key, fingerprint, job)
                    if body:
                        body["updating"] = True
        except ApiError:
            raise
        except Exception:
            # Nie udało się zlecić liczenia: zapisany zestaw i tak pokazujemy, bez niego - 503 (strona ponowi)
            log.exception("Nie udało się zlecić liczenia zestawu %s", key)
            results.release(user_id, key, fingerprint)
            if body is None:
                raise ApiError(503, "Nie udało się przygotować propozycji – spróbuj za chwilę.")
    return body  # None -> 202, strona zapyta ponownie


def _stored(item: dict | None, fingerprint: str, now: datetime) -> tuple[dict | None, bool]:
    """(zestaw do pokazania albo None, czy jest aktualny). Zestaw dla innych preferencji się nie nadaje;
    nieaktualny (starszy niż RESULTS_MAX_AGE albo z małą liczbą trwających wydarzeń) - nadaje się
    do pokazania, dopóki w tle liczy się nowy."""
    if not item or "body" not in item or item.get("prefsHash") != fingerprint:
        return None, False
    body = json.loads(item["body"])
    items = [c for c in body["items"] if still_on(c, now)]  # zestaw na dziś ogląda się do wieczora
    if body["items"] and not items:
        return None, False
    age = now - datetime.fromisoformat(body["generatedAt"])
    fresh = (age <= RESULTS_MAX_AGE and len(items) >= min(MIN_RESULTS, len(body["items"]))
             and body.get("resultsVersion", 1) >= RESULTS_VERSION)  # starsza wersja: pokaż, policz od nowa
    refining = bool(body.pop("refining", False)) and age.total_seconds() < REFINE_SECONDS
    return {**body, "items": items, "cached": True, "updating": refining or claimed(item, now)}, fresh


def _start_compute(user_id: str, key: str, fingerprint: str, job: dict) -> None:
    """Liczenie w tle: asynchroniczne wywołanie tej samej Lambdy (lokalnie: wątek)."""
    payload = {"action": "compute", "userId": user_id, **job}
    try:
        if name := os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            lambda_client.invoke(FunctionName=name, InvocationType="Event", Payload=json.dumps(payload))
        else:
            threading.Thread(target=handler, args=(payload, None), daemon=True).start()
    except Exception:
        results.release(user_id, key, fingerprint)
        raise


def _compute_inline(user_id: str, user: dict, key: str, fingerprint: str, job: dict, now: datetime) -> None:
    """Faza 1 (filtry + wektory) policzona od razu w bieżącej, ciepłej Lambdzie i zapisana.
    Używana tylko, gdy _engine już jest w pamięci (bez ryzyka zimnego startu w ścieżce GET)."""
    span = (date.fromisoformat(job["from"]), date.fromisoformat(job["to"]))
    body, _context, found = compute(_engine, user["preferences"], user.get("ragProfile"), span,
                                    job.get("q", ""), job.get("limit", DEFAULT_LIMIT), now, job["when"])
    refine_it = LLM_ENABLED and _engine.client is not None and bool(found)
    results.put(user_id, key, fingerprint, {**body, "refining": refine_it}, expires_at(span))


def compute_set(event: dict) -> dict:
    """Jeden zestaw zlecony przez GET (claim już jest)."""
    user = users.get_item(Key={"userId": event["userId"]}, ConsistentRead=True).get("Item") or {}
    span = (date.fromisoformat(event["from"]), date.fromisoformat(event["to"]))
    key = set_key(event["when"], span, event.get("q", ""), event["limit"])
    if not user.get("preferences"):
        return {"computed": 0}
    done = _compute_sets(event["userId"], user["preferences"], user.get("ragProfile"),
                         [(event["when"], span, key)], event.get("q", ""), event["limit"], datetime.now(WARSAW))
    return {"computed": done}


def precompute(user_id: str | None = None, context=None) -> dict:
    """Zestawy na dziś, jutro i weekend: dla jednej osoby (po zmianie profilu, przy logowaniu) albo dla
    wszystkich aktywnych w ostatnich PRECOMPUTE_ACTIVE_DAYS dniach (w nocy). Aktualne zestawy zostają."""
    if user_id:
        item = users.get_item(Key={"userId": user_id}, ConsistentRead=True).get("Item")
        todo = [item] if item and item.get("preferences") else []
    else:
        todo = _active_users()

    stats = {"users": 0, "computed": 0, "reused": 0, "busy": 0, "stopped": False}
    for user in todo:
        if context and context.get_remaining_time_in_millis() < 120_000:
            stats["stopped"] = True  # reszta policzy się przy wejściu na stronę
            break
        stats["users"] += 1
        uid, prefs, rag = user["userId"], user["preferences"], user.get("ragProfile")
        fingerprint = prefs_hash(prefs, rag)
        now = datetime.now(WARSAW)
        jobs = []
        for when in DEFAULT_SETS:
            span = window(when, now.date())
            key = set_key(when, span, "", DEFAULT_LIMIT)
            if _stored(results.get(uid, key), fingerprint, now)[1]:
                stats["reused"] += 1
            elif results.claim(uid, key, fingerprint, now):
                jobs.append((when, span, key))
            else:
                stats["busy"] += 1  # liczy go już ktoś inny (np. strona otwarta zaraz po zmianie profilu)
        stats["computed"] += _compute_sets(uid, prefs, rag, jobs, "", DEFAULT_LIMIT, now)
    log.info("Przeliczenie zestawów: %s", stats)
    return stats


def _compute_sets(user_id, prefs, rag_profile, jobs, query, limit, now) -> int:
    """Liczy zestawy, na które mamy claim: 1) od razu zapisuje kolejność wektorową z uzasadnieniem
    z reguł, 2) potem AI układa kolejność i pisze uzasadnienia (równolegle dla kilku zestawów)."""
    if not jobs:
        return 0
    fingerprint = prefs_hash(prefs, rag_profile)
    try:
        engine = _current_engine()
    except Exception:
        for _, _, key in jobs:
            results.release(user_id, key, fingerprint)
        raise
    use_llm = LLM_ENABLED and engine.client is not None

    first = []
    for when, span, key in jobs:
        try:
            body, context, found = compute(engine, prefs, rag_profile, span, query, limit, now, when)
        except Exception:
            log.exception("Nie udało się policzyć zestawu %s", key)
            results.release(user_id, key, fingerprint)
            continue
        refine_it = use_llm and bool(found)
        results.put(user_id, key, fingerprint, {**body, "refining": refine_it}, expires_at(span))
        if refine_it:
            first.append((key, span, body, context, found))

    def finish(job):
        key, span, body, context, found = job
        started = time.monotonic()
        # Fraza od użytkownika: AI najpierw rozwija ją (recommender/expand.py) i wybieramy kandydatów
        # jeszcze raz - w fazie 1 tego nie robimy, żeby pierwsze karty były od razu.
        expanded = engine.expand(context) if context.get("query") else context
        pool = engine.retriever.retrieve(expanded, top_k=limit) if expanded is not context else found
        ranked = engine.rerank(expanded, pool)
        log.info("AI dla %s: %s%s w %.1f s", key, "OK" if ranked else f"brak ({engine.last_error})",
                 " (fraza rozwinięta)" if expanded is not context else "", time.monotonic() - started)
        items = ranked or (pool if expanded is not context else None)
        better = {**body, "ranking": "llm" if ranked else body["ranking"], "items": [card(c, query) for c in items]} if items else body
        results.put(user_id, key, fingerprint, {**better, "refining": False}, expires_at(span))

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(finish, first))
    return len(jobs)


def compute(engine, prefs, rag_profile, span, query, limit, now, when) -> tuple[dict, dict, list]:
    """Faza 1: filtry + podobieństwo wektorowe. -> (zestaw kart, user_context, kandydaci dla AI)"""
    first_area = start_area(prefs)
    query_vector = None
    for area in AREAS[AREAS.index(first_area):]:
        context = build_context(prefs, rag_profile, span, query, now, area)
        # Wektor zapytania zależy tylko od frazy i zainteresowań, nie od obszaru - liczymy go raz,
        # a pętla po obszarach (okolica -> sąsiednie -> całe miasto) zmienia tylko twardy filtr dzielnicy.
        if query_vector is None:
            query_vector = engine.retriever.encoder.encode(context)
        if len(engine.retriever.retrieve(context, top_k=MIN_RESULTS, query_vector=query_vector)) >= MIN_RESULTS:
            break
    found = engine.recommend(context, top_k=limit, explain=False, expand=False, query_vector=query_vector)
    log.info("Rekomendacje: when=%s area=%s query=%s -> %d", when, area, bool(query), len(found))
    body = {
        "generatedAt": now.isoformat(timespec="seconds"),
        "when": when,
        "window": {"from": context["date_from"], "to": context["date_to"]},
        "query": query or None,
        "district": prefs.get("district"),
        "area": area,
        "areaRelaxed": area != first_area,
        "ranking": "cosine",
        "items": [card(c, query) for c in found],
        "index": {"builtAt": _engine_meta.get("builtAt"), "events": _engine_meta.get("events")},
        "resultsVersion": RESULTS_VERSION,
    }
    return body, context, found


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
    global _engine, _engine_version, _engine_meta, _checked_at, _rejected_version
    if _engine is not None and time.monotonic() - _checked_at < INDEX_CHECK_SECONDS:
        return _engine
    _checked_at = time.monotonic()
    version = store.version()
    if version is not None and version not in (_engine_version, _rejected_version):
        index = store.load()
        if index is not None and index.meta.get("model") != DEFAULT_MODEL:
            # Np. zaraz po wdrożeniu obrazu z nowym modelem: wektory mają inny wymiar niż zapytania.
            # Zapisane zestawy dalej się wyświetlają; liczenie ruszy po przebudowie indeksu.
            log.warning("Indeks z modelem %s, obraz ma %s - czekam na przebudowę (scripts/recommender-refresh.sh)",
                        index.meta.get("model"), DEFAULT_MODEL)
            _rejected_version, index = version, None
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

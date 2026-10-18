#!/usr/bin/env python
"""Benchmark: how long each stage of a recommendation request actually takes.

Times the real pipeline (real mpnet model, real chunker/retriever/ranker code and the
real `handler.compute` / `handler.get_recommendations` code paths) stage by stage, on a
synthetic corpus the size of the production table, so a change can be judged by numbers
instead of feel:

    .venv/bin/python scripts/bench-recommender.py                  # ~1200 events, LLM skipped
    .venv/bin/python scripts/bench-recommender.py --events 300 --repeats 5
    .venv/bin/python scripts/bench-recommender.py --llm            # + real DeepSeek calls
    .venv/bin/python scripts/bench-recommender.py --travel local   # narrow profile (more relaxed area loop)

No AWS and no network are touched: the handler is imported with INDEX_PATH (a local
index file) and an in-memory results store, and the users table is stubbed. Nothing
leaves the machine.

Caveat: numbers are local x86 CPU with a warm page cache, not the Lambda (arm64,
3008 MB). Use them for the phase-1/phase-2 split and for before/after comparisons,
not as absolute production latencies. Without a DEEPSEEK_API_KEY the two LLM calls
are not made; their prompt sizes are still reported, and LLM latency scales with them.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import importlib.util
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "recommender_api"))

os.environ.setdefault("AWS_DEFAULT_REGION", "eu-central-1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("LLM_ENABLED", "true")

WARSAW = ZoneInfo("Europe/Warsaw")
DISTRICTS = ["Śródmieście", "Wola", "Mokotów", "Praga-Północ", "Ochota", "Żoliborz", "Bemowo", "Wilanów"]
# Distinct closing sentences so every clone gets its own embedding text (real data: 1200 distinct texts).
FLAVOUR = [
    "Kameralna sala, miejsca siedzące, wstęp po rejestracji.",
    "Spotkanie poprowadzi doświadczony instruktor z wieloletnią praktyką.",
    "Po wydarzeniu rozmowa z twórcami i poczęstunek dla uczestników.",
    "Zajęcia odbywają się w małych grupach, sprzęt zapewnia organizator.",
    "Wydarzenie jest częścią cyklu cotygodniowych spotkań dzielnicowych.",
    "Materiały do pracy własnej dostępne po zakończeniu spotkania.",
    "Wstęp wolny, ale liczba miejsc jest ograniczona, warto przyjść wcześniej.",
    "Organizator zapewnia tłumaczenie na język migowy na życzenie.",
    "Spotkanie w przestrzeni dostępnej dla osób poruszających się na wózku.",
    "Po części głównej zapraszamy na wspólne rozmowy i kawę.",
    "Wydarzenie dedykowane osobom, które zaczynają swoją przygodę z tematem.",
    "Program obejmuje pokaz, ćwiczenia praktyczne i dyskusję z ekspertem.",
    "We współpracy z lokalną biblioteką i domem kultury.",
    "Zapisy przez stronę organizatora, bilety także w kasie na miejscu.",
    "Wydarzenie odbędzie się bez względu na pogodę.",
    "Na miejscu dostępny bufet z napojami i przekąskami.",
]


# --------------------------------------------------------------------------- #
# Timing helpers
# --------------------------------------------------------------------------- #
class Timer:
    """Collects (label, ms, note) rows and prints them as an aligned block."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, float, str]] = []

    def add(self, label: str, ms: float, note: str = "") -> None:
        self.rows.append((label, ms, note))

    def measure(self, label: str, fn, repeats: int = 1, note: str = "") -> float:
        samples, result = [], None
        for _ in range(max(repeats, 1)):
            started = time.perf_counter()
            result = fn()
            samples.append((time.perf_counter() - started) * 1000)
        suffix = f"median of {repeats}" if repeats > 1 else "1 run"
        self.add(label, statistics.median(samples), f"{note} [{suffix}]".strip())
        return result  # type: ignore[return-value]

    def section(self, title: str) -> None:
        print(f"\n== {title} ==")

    def flush(self, indent: str = "  ") -> None:
        width = max((len(label) for label, _, _ in self.rows), default=0)
        for label, ms, note in self.rows:
            value = f"{ms / 1000:7.2f} s" if ms >= 1000 else f"{ms:7.1f} ms"
            print(f"{indent}{label:<{width}}  {value}   {note}".rstrip())
        self.rows.clear()


def human_bytes(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB" if n >= 1_048_576 else f"{n / 1024:.0f} kB"


def approx_tokens(obj) -> int:
    """Rough token estimate for a Polish/JSON payload (~3.5 chars per token)."""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return int(len(text) / 3.5)


# --------------------------------------------------------------------------- #
# Corpus: the hand-written demo dataset, cloned to production size
# --------------------------------------------------------------------------- #
def load_demo_events() -> list[dict]:
    path = ROOT / "scripts" / "recommender-demo.py"
    spec = importlib.util.spec_from_file_location("bench_demo_events", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # main() is guarded by __name__
    return module.EVENTS


def make_corpus(size: int) -> list[dict]:
    """Clone the demo events to `size` records, spreading occurrences over the next week."""
    base = load_demo_events()
    today = datetime.now(WARSAW).date()
    events = []
    for i in range(size):
        source = base[i % len(base)]
        event = copy.deepcopy(source)
        event["id"] = f"{source['id']}-{i // len(base)}"
        # Unique title + lead per clone, otherwise dedupe_events() collapses them and the corpus
        # behaves like 25 events instead of 1200.
        event["title"] = f"{source['title']} – edycja {i + 1}"
        day = today + timedelta(days=i % 7)
        start = datetime.combine(day, dtime(hour=10 + (i % 12)), tzinfo=WARSAW)
        event["occurrences"] = [{"start": start.isoformat(), "end": (start + timedelta(hours=2)).isoformat()}]
        event["district"] = [{"name": DISTRICTS[i % len(DISTRICTS)]}]
        event["venue"] = {"name": f"{source['venue']['name']} {i // len(base)}"}
        # Unique embedding text per clone, at a realistic length (like the 1200 real events).
        event["lead"] = f"{source.get('lead', '')} {FLAVOUR[i % len(FLAVOUR)]} Edycja {i}."
        events.append(event)
    return events


def fake_prefs(travel: str) -> dict:
    """A realistic onboarding profile (keys as in src/client_api/onboarding.py)."""
    return {
        "district": "Śródmieście",
        "travelRange": travel,
        "themes": ["Muzyka", "Sztuki wizualne"],
        "formats": ["Koncert", "Wystawa"],
        "cost": "Bezpłatne",
        "mode": "Stacjonarne",
        "audience": "Dorośli (18-64)",
        "occasion": ["Na randkę"],
        "activityLevel": ["Spokojnie"],
        "setting": ["W pomieszczeniu"],
        "registration": ["Bez zapisów"],
        "accessibility": [],
        "timeOfDay": ["wieczór"],
        "maxPrice": 50,
    }


# --------------------------------------------------------------------------- #
# 1. Cold start: torch import + model load (once per Lambda instance)
# --------------------------------------------------------------------------- #
def bench_cold_start(t: Timer):
    t.section("Cold start (fresh process, model baked into the image)")
    t.measure("import torch", lambda: importlib.import_module("torch"))
    t.measure("import sentence_transformers", lambda: importlib.import_module("sentence_transformers"))

    from recommender.embedder import EmbeddingModel

    t.measure("EmbeddingModel() load (weights -> RAM)", lambda: EmbeddingModel())
    model = EmbeddingModel()
    t.measure("first encode after load (lazy kernel init)", lambda: model.encode(["rozgrzewka"]))
    t.flush()
    print(f"  (torch threads: {importlib.import_module('torch').get_num_threads()})")
    return model


# --------------------------------------------------------------------------- #
# 2. Index build / load
# --------------------------------------------------------------------------- #
def bench_index(t: Timer, events: list[dict], model, store_path: Path):
    from index_store import Index, refresh, text_hash

    from recommender import DEFAULT_MODEL, chunk_events

    t.section(f"Index build ({len(events)} events)")
    started = time.perf_counter()
    chunks = chunk_events(events)
    hashes = [text_hash(c.text, DEFAULT_MODEL) for c in chunks]
    t.add("chunk_events + text_hash", (time.perf_counter() - started) * 1000, f"{len(chunks)} chunks")
    del hashes

    # Cold build = embed every chunk (what a full re-index / model swap costs).
    started = time.perf_counter()
    index, cold_stats = refresh(events, None, lambda: model)
    cold_ms = (time.perf_counter() - started) * 1000
    rate = cold_stats["embedded"] / (cold_ms / 1000) if cold_stats["embedded"] else 0.0
    t.add("refresh() cold: embed all chunks", cold_ms, f"{cold_stats['embedded']} texts, {rate:.1f} texts/s")

    started = time.perf_counter()
    _, same_stats = refresh(events, index, lambda: model)
    t.add(
        "refresh() unchanged (digest hit)", (time.perf_counter() - started) * 1000, f"{same_stats['embedded']} embedded"
    )

    changed = events + make_corpus(len(events) + 5)[-5:]
    started = time.perf_counter()
    _, new_stats = refresh(changed, index, lambda: model)
    t.add("refresh() +5 new events", (time.perf_counter() - started) * 1000, f"{new_stats['embedded']} embedded")

    started = time.perf_counter()
    data = index.to_bytes()
    serialize_ms = (time.perf_counter() - started) * 1000
    store_path.write_bytes(data)
    t.add("npz serialize -> file", serialize_ms, human_bytes(len(data)))

    started = time.perf_counter()
    loaded = Index.from_bytes(store_path.read_bytes())
    t.add("npz load <- file (~= S3 download + parse)", (time.perf_counter() - started) * 1000, human_bytes(len(data)))
    t.flush()
    return loaded, cold_stats


# --------------------------------------------------------------------------- #
# 3. Engine build (per cold instance)
# --------------------------------------------------------------------------- #
def bench_engine(t: Timer, events: list[dict], model, index, llm: bool):
    from recommender import Recommender
    from recommender.chunker import build_event_text

    t.section("Engine build (once per cold instance; a warm one skips it)")
    vi = t.measure("Index.vector_index()", index.vector_index, 1, f"{len(index.chunk_ids)} rows")
    t.rows.clear()
    started = time.perf_counter()
    vi = index.vector_index()
    t.add("Index.vector_index()", (time.perf_counter() - started) * 1000, f"{len(vi)} rows, dim {vi.dim}")

    started = time.perf_counter()
    by_id = {e.get("id", ""): build_event_text(e) for e in events}
    t.add("build_event_text per event (Retriever init)", (time.perf_counter() - started) * 1000, f"{len(by_id)} events")

    api_key = None
    if llm:
        from handler import _deepseek_key

        api_key = _deepseek_key()
        if not api_key:
            print("  ! --llm given but no DEEPSEEK_API_KEY found -> LLM steps will be skipped")

    started = time.perf_counter()
    engine = Recommender(events, model=model, api_key=api_key, index=vi, llm_timeout=20)
    t.add(
        "Recommender(...) total",
        (time.perf_counter() - started) * 1000,
        "LLM client ready" if engine.client else "no LLM key",
    )
    t.flush()
    return engine


# --------------------------------------------------------------------------- #
# 4. Phase 1: filters + vectors for one search
# --------------------------------------------------------------------------- #
def bench_phase1(t: Timer, engine, prefs, reps: int, query: str) -> None:
    from user_context import build_context, window

    from handler import compute
    from recommender.retriever import make_event_filter

    now = datetime.now(WARSAW)
    span = window("week", now.date())
    context = build_context(prefs, "profil testowy", span, query, now, "city")

    t.section(f"Phase 1: filters + vectors (query={query!r})")
    t.measure("query encode (1 short string)", lambda: engine.retriever.encoder.encode(context), reps)

    def filtering():
        predicate = make_event_filter(context)
        return {e.get("id", "") for e in engine.events if predicate(e)}

    allowed = filtering()
    t.measure("hard filters over all events", filtering, reps, f"{len(allowed)}/{len(engine.events)} pass")

    qv = engine.retriever.encoder.encode(context)
    vector_index = engine.retriever.index
    t.measure(
        "cosine over allowed chunks",
        lambda: vector_index.query(qv, k=len(vector_index), allow=allowed),
        reps,
        f"{len(vector_index)} chunks, {vector_index.dim}-dim",
    )
    t.measure(
        "retrieve() total",
        lambda: engine.retriever.retrieve(context, top_k=16),
        reps,
        "filters + encode + cosine + boosts + dedupe + diversify",
    )

    calls = {"n": 0}
    original = engine.retriever.encoder.encode

    def counting(ctx):
        calls["n"] += 1
        return original(ctx)

    engine.retriever.encoder.encode = counting  # type: ignore[method-assign]
    try:
        result = t.measure(
            "compute() = real handler phase 1",
            lambda: compute(engine, prefs, "profil testowy", span, query, 16, now, "week"),
            reps,
            "area loop + card building, whole phase 1",
        )
    finally:
        engine.retriever.encoder.encode = original  # type: ignore[method-assign]
    body = result[0]
    print(f"  -> query encodes inside one compute(): {calls['n'] / max(reps, 1):.1f}x per request (redundant)")
    print(f"  (result: area={body['area']} relaxed={body['areaRelaxed']} cards={len(body['items'])})")
    t.flush()
    return context


# --------------------------------------------------------------------------- #
# 5. Phase 2: DeepSeek expansion + re-rank
# --------------------------------------------------------------------------- #
def bench_phase2(t: Timer, engine, context) -> None:
    from recommender.expand import _SYSTEM as EXPAND_SYSTEM
    from recommender.ranker import _candidate_payload, _prefs_payload

    found = engine.retriever.retrieve(context, top_k=16)
    t.section("Phase 2: DeepSeek (expansion + re-rank), runs in the background")
    if engine.client is None:
        print("  (no DeepSeek key: payload sizes + local overhead only)")

    if engine.client is not None:
        t.measure("expand(): LLM call #1", lambda: engine.expand(context), 3, f"{(engine.last_expansion or '')[:40]!r}")
        expanded = engine.expand(context)
        t.measure("re-retrieve with expanded query", lambda: engine.retriever.retrieve(expanded, top_k=16), 3)
        pool = engine.retriever.retrieve(expanded, top_k=16)
        t.measure(
            "rerank(): LLM call #2",
            lambda: engine.rerank(expanded, pool),
            3,
            f"ok={engine.last_error is None}, {(engine.last_usage or {}).get('total_tokens')} tokens",
        )

    candidates = _candidate_payload(found)
    prefs_payload = _prefs_payload(context)
    t.measure(
        "build rerank payload (no network)", lambda: _candidate_payload(found), 7, f"{len(candidates)} candidates"
    )
    print(f"  expand(): ~{approx_tokens(EXPAND_SYSTEM) + 40} prompt tokens, ~40 completion tokens, 1 roundtrip")
    print(
        f"  rerank(): ~{approx_tokens(prefs_payload) + approx_tokens(candidates)} prompt tokens, "
        f"~{len(candidates) * 20} completion tokens ({len(candidates)} reasons), 1 roundtrip"
    )
    print(f"  rerank candidate list: {len(candidates)} events x ~300 chars of lead (rank_candidates payload)")
    t.flush()


# --------------------------------------------------------------------------- #
# 6. The GET path, end to end, with the in-memory store
# --------------------------------------------------------------------------- #
def bench_get_path(t: Timer, engine, prefs, reps: int, llm: bool) -> None:
    from user_context import window

    import handler

    class FakeUsers:
        def get_item(self, **_kwargs):
            return {"Item": {"userId": "bench-user", "preferences": prefs, "ragProfile": "profil testowy"}}

    handler.users = FakeUsers()
    handler._engine = engine
    handler._engine_version = "bench"
    handler._engine_meta = {"builtAt": "bench", "events": len(engine.events)}
    handler._checked_at = time.monotonic() + 10_000  # never re-check S3 inside this benchmark
    handler.LLM_ENABLED = llm and engine.client is not None

    params = {"when": "week", "q": "jazz", "limit": "16"}
    span = window("week", datetime.now(WARSAW).date())
    key = handler.set_key("week", span, params["q"], 16)

    t.section("GET /api/recommendations, end to end (local: in-memory store, no HTTP/Lambda)")
    started = time.perf_counter()
    first = handler.get_recommendations("bench-user", params)  # warm: phase 1 inline + async refine
    claim_ms = (time.perf_counter() - started) * 1000
    t.add(
        "GET, first request (warm: phase 1 inline)",
        claim_ms,
        f"cached={bool(first and first.get('cached'))}, updating={first and first.get('updating')}",
    )

    deadline = time.monotonic() + 120  # background thread computes phase 1 (cold path) / refines (warm path)
    while True:
        stored = handler.results.get("bench-user", key)
        if stored is not None and "body" in stored:
            break  # the claim record itself is stored immediately, the body comes later
        if time.monotonic() > deadline:
            raise RuntimeError("phase 1 did not store a set within 120 s")
        time.sleep(0.005)
    ready_ms = (time.perf_counter() - started) * 1000
    t.add("...until the phase-1 set is stored", ready_ms, "what a new query waits for today")

    cached = handler.get_recommendations("bench-user", params)
    t.measure(
        "GET, set already stored",
        lambda: handler.get_recommendations("bench-user", params),
        reps,
        f"cached={bool(cached and cached.get('cached'))}, updating={cached and cached.get('updating')}",
    )
    t.flush()

    print(f"\n  New query, cold instance: 202 -> front sleeps retryAfter 2 s -> {ready_ms:.0f} ms of work -> 200.")
    print(f"  New query, warm instance: cards inline in ~{claim_ms:.0f} ms (no 2 s poll), AI refines behind it.")
    print("  Same query again: instant (stored set).")


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Stage-by-stage latency benchmark of the recommender.")
    parser.add_argument("--events", type=int, default=1200, help="corpus size (production table ~1200)")
    parser.add_argument("--repeats", type=int, default=7, help="runs per micro-benchmark (median reported)")
    parser.add_argument("--query", default="jazz", help="search query for the phase benchmarks")
    parser.add_argument("--llm", action="store_true", help="make real DeepSeek calls (needs DEEPSEEK_API_KEY)")
    parser.add_argument("--travel", default="city", choices=["local", "nearby", "city"], help="profile travelRange")
    args = parser.parse_args()

    import numpy as np

    print(
        f"python {sys.version.split()[0]}  numpy {np.__version__}  events={args.events}  "
        f"travelRange={args.travel}  llm={'on' if args.llm else 'off'}"
    )
    print(f"corpus: {len(make_corpus(args.events))} cloned demo events, occurrences spread over the next 7 days")

    t = Timer()
    prefs = fake_prefs(args.travel)
    events = make_corpus(args.events)

    model = bench_cold_start(t)
    with tempfile.TemporaryDirectory() as tmp:
        store_path = Path(tmp) / "index.npz"
        os.environ["INDEX_PATH"] = str(store_path)  # handler store = FileStore, no S3
        index, _cold_stats = bench_index(t, events, model, store_path)
        engine = bench_engine(t, events, model, index, args.llm)
        context = bench_phase1(t, engine, prefs, args.repeats, args.query)
        bench_phase2(t, engine, context)
        bench_get_path(t, engine, prefs, args.repeats, args.llm)

    print("\nHow to read this:")
    print("  * cold start + index load happen once per Lambda instance, before any phase;")
    print("  * phase 1 is what a *new* search must wait for (today: 202 + a 2 s front poll + this);")
    print("  * phase 2 always runs in the background and only reorders/explains the cards.")


if __name__ == "__main__":
    main()
